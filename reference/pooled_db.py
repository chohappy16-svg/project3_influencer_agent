"""
DBUtils `dbutils.pooled_db.PooledDB` 구현 모듈
- mincached 만큼 초기 유휴 커넥션을 미리 생성
- pool.connection() 호출 시 풀에서 커넥션을 대여
- conn.close() 호출 시 연결을 끊지 않고 커넥션 풀(maxcached 이하)로 반납하여 재사용!
"""

import queue
import threading
from typing import Any


class TooManyConnections(Exception):
    """maxconnections 한도를 초과했을 때(blocking=False) 발생하는 예외"""


class PooledDBConnection:
    """
    커넥션 풀에서 대여된 연결 래퍼 객체.
    finally 블록에서 `conn.close()`를 호출하면 실제 DB 연결을 종료하지 않고
    커넥션 풀(Pool)로 반납합니다.
    """

    def __init__(self, pool: "PooledDB", raw_conn: Any):
        self._pool = pool
        self._raw_conn = raw_conn
        self._closed = False

    def cursor(self, *args, **kwargs):
        if self._pool.ping & 2:
            self._ensure_alive()
        return self._raw_conn.cursor(*args, **kwargs)

    def commit(self):
        return self._raw_conn.commit()

    def rollback(self):
        return self._raw_conn.rollback()

    def ping(self, reconnect: bool = True):
        if hasattr(self._raw_conn, "ping"):
            return self._raw_conn.ping(reconnect=reconnect)
        return True

    def _ensure_alive(self):
        if hasattr(self._raw_conn, "ping"):
            try:
                self._raw_conn.ping(reconnect=True)
            except Exception:
                pass

    def close(self):
        """실제 연결을 끊지 않고 커넥션 풀(PooledDB)에 반납합니다."""
        if not self._closed:
            self._closed = True
            self._pool._return_connection(self._raw_conn)

    def _force_close(self):
        try:
            self._raw_conn.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class PooledDB:
    """
    PyMySQL 등 DB-API 2.0 모듈을 위한 커넥션 풀(Connection Pool) 클래스
    """

    def __init__(
        self,
        creator: Any = None,
        mincached: int = 0,
        maxcached: int = 0,
        maxshared: int = 0,
        maxconnections: int = 0,
        blocking: bool = False,
        maxusage: int = 0,
        setsession=None,
        reset: bool = True,
        failures=None,
        ping: int = 1,
        **kwargs,
    ):
        # 수업 필기 오타(`creater = pymysql`)도 호환되도록 처리
        if creator is None and "creater" in kwargs:
            creator = kwargs.pop("creater")
        if creator is None:
            raise ValueError("creator (예: pymysql) 모듈을 지정해야 합니다.")

        self._creator = creator
        self.mincached = max(0, int(mincached or 0))
        self.maxcached = max(0, int(maxcached or 0))
        self.maxconnections = max(0, int(maxconnections or 0))
        self.blocking = bool(blocking)
        self.ping = int(ping if ping is not None else 1)
        self._db_kwargs = kwargs

        if self.maxcached > 0 and self.mincached > self.maxcached:
            self.mincached = self.maxcached

        self._lock = threading.Lock()
        self._idle_cache: queue.Queue = queue.Queue(maxsize=self.maxcached or 0)
        self._semaphore = (
            threading.BoundedSemaphore(self.maxconnections)
            if self.maxconnections > 0
            else None
        )

        # 커넥션 풀 모니터링 통계
        self.created_connections = 0
        self.active_connections = 0
        self.total_borrowed = 0
        self.total_returned = 0

        # mincached 개수만큼 초기 대기 연결 미리 생성
        initial_conns = []
        for _ in range(self.mincached):
            try:
                raw = self._create_raw_connection()
                initial_conns.append(raw)
            except Exception:
                break

        for raw in initial_conns:
            try:
                self._idle_cache.put_nowait(raw)
            except queue.Full:
                self._close_raw(raw)

    def _create_raw_connection(self):
        if hasattr(self._creator, "connect"):
            conn = self._creator.connect(**self._db_kwargs)
        elif callable(self._creator):
            conn = self._creator(**self._db_kwargs)
        else:
            raise TypeError("creator는 connect() 메서드를 가진 모듈이거나 호출 가능한 객체여야 합니다.")
        with self._lock:
            self.created_connections += 1
        return conn

    def _close_raw(self, raw_conn: Any):
        try:
            raw_conn.close()
        except Exception:
            pass

    def connection(self) -> PooledDBConnection:
        """커넥션 풀에서 연결을 하나 빌려옵니다 (대여)."""
        if self._semaphore is not None:
            acquired = self._semaphore.acquire(blocking=self.blocking)
            if not acquired:
                raise TooManyConnections("커넥션 풀의 최대 연결 수(maxconnections)를 초과했습니다.")

        try:
            try:
                raw_conn = self._idle_cache.get_nowait()
            except queue.Empty:
                raw_conn = self._create_raw_connection()

            # ping=1 (풀에서 연결을 빌릴 때 연결 확인 및 자동 재연결)
            if (self.ping & 1) and hasattr(raw_conn, "ping"):
                try:
                    raw_conn.ping(reconnect=True)
                except Exception:
                    self._close_raw(raw_conn)
                    raw_conn = self._create_raw_connection()

            with self._lock:
                self.active_connections += 1
                self.total_borrowed += 1

            return PooledDBConnection(self, raw_conn)
        except Exception:
            if self._semaphore is not None:
                self._semaphore.release()
            raise

    def _return_connection(self, raw_conn: Any):
        """사용이 끝난 연결을 끊지 않고 커넥션 풀로 반납합니다."""
        try:
            # 미완료 트랜잭션 초기화
            try:
                raw_conn.rollback()
            except Exception:
                pass

            if self.maxcached == 0 or self._idle_cache.qsize() < self.maxcached:
                try:
                    self._idle_cache.put_nowait(raw_conn)
                except queue.Full:
                    self._close_raw(raw_conn)
            else:
                self._close_raw(raw_conn)
        finally:
            with self._lock:
                self.active_connections = max(0, self.active_connections - 1)
                self.total_returned += 1
            if self._semaphore is not None:
                self._semaphore.release()

    def status(self) -> dict:
        """현재 커넥션 풀 상태 정보를 반환합니다."""
        return {
            "maxconnections": self.maxconnections,
            "mincached": self.mincached,
            "maxcached": self.maxcached,
            "blocking": self.blocking,
            "ping": self.ping,
            "idle_cached": self._idle_cache.qsize(),
            "active_in_use": self.active_connections,
            "total_created": self.created_connections,
            "total_borrowed": self.total_borrowed,
            "total_returned": self.total_returned,
        }

    def close(self):
        """풀 안의 모든 대기 연결을 정리합니다."""
        while not self._idle_cache.empty():
            try:
                raw = self._idle_cache.get_nowait()
                self._close_raw(raw)
            except queue.Empty:
                break


# 수업 필기 오타(PoolDB, PooldeDB) 호환 별칭
PoolDB = PooledDB
PooldeDB = PooledDB

