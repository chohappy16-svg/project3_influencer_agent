/**
 * [InfluenceOps] frontend/src/api/client.js
 * ==============================================================================
 * 백엔드 REST API 통신용 통합 Axios 클라이언트
 *
 * 주요 기능:
 *   1. JWT 인증 헤더 자동 주입: localStorage에 저장된 토큰을 모든 요청에 자동 첨부
 *   2. authApi: 회원가입, 로그인, 내 정보 조회, 브랜드 DNA 업데이트
 *   3. campaignsApi: 캠페인 CRUD, 소프트 삭제/복원/영구삭제, 후보 업로드(멀티파트),
 *      분석 결과 조회, 다자 비교, 최종 승인/취소 상태 변경, 엑셀 다운로드
 * ==============================================================================
 */

import axios from 'axios';

// 브라우저 접속 호스트(localhost, EC2 공인 IP 등)에 맞춰 동적으로 백엔드 포트(8001)에 연결
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ||
  (typeof window !== 'undefined' && window.location.hostname
    ? `${window.location.protocol}//${window.location.hostname}:8001`
    : 'http://127.0.0.1:8001');

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('influenceops_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const authApi = {
  signup: (payload) => apiClient.post('/api/auth/signup', payload).then((r) => r.data),
  login: (payload) => apiClient.post('/api/auth/login', payload).then((r) => r.data),
  getMe: () => apiClient.get('/api/auth/me').then((r) => r.data),
  updateBrandDna: (payload) => apiClient.put('/api/auth/brand-dna', payload).then((r) => r.data),
};

export const campaignsApi = {
  list: (trash = false) =>
    apiClient.get('/api/campaigns', { params: { trash } }).then((r) => r.data),
  create: (payload) => apiClient.post('/api/campaigns', payload).then((r) => r.data),
  update: (campaignId, payload) =>
    apiClient.patch(`/api/campaigns/${campaignId}`, payload).then((r) => r.data),
  softDelete: (campaignId) =>
    apiClient.delete(`/api/campaigns/${campaignId}`).then((r) => r.data),
  restore: (campaignId) =>
    apiClient.post(`/api/campaigns/${campaignId}/restore`).then((r) => r.data),
  permanentDelete: (campaignId) =>
    apiClient.delete(`/api/campaigns/${campaignId}/permanent`).then((r) => r.data),
  upload: (campaignId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiClient
      .post(`/api/campaigns/${campaignId}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data);
  },
  getResults: (campaignId) => apiClient.get(`/api/campaigns/${campaignId}/results`).then((r) => r.data),
  compare: (campaignId, ids) =>
    apiClient.get(`/api/campaigns/${campaignId}/compare`, { params: { ids: ids.join(',') } }).then((r) => r.data),
  decide: (resultId, decision) =>
    apiClient.patch(`/api/results/${resultId}/decision`, { decision }).then((r) => r.data),
  deleteResult: (resultId) =>
    apiClient.delete(`/api/results/${resultId}`).then((r) => r.data),
  exportExcel: async (campaignId) => {
    const res = await apiClient.get(`/api/campaigns/${campaignId}/export`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `influenceops_campaign_${campaignId}_approved.xlsx`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

export default apiClient;
