import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: `${API_BASE}/api`,
  headers: { "Content-Type": "application/json" },
});

// ── Request interceptor: attach JWT access token ──────────────────────────
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// ── Response interceptor: auto-refresh on 401 ─────────────────────────────
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const { data } = await axios.post(`${API_BASE}/api/auth/refresh`, {
            refresh_token: refreshToken,
          });
          localStorage.setItem("access_token", data.access_token);
          localStorage.setItem("refresh_token", data.refresh_token);
          original.headers.Authorization = `Bearer ${data.access_token}`;
          return api(original);
        } catch {
          localStorage.clear();
          window.location.href = "/login";
        }
      } else {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ── Typed API helpers ──────────────────────────────────────────────────────

export const auth = {
  register: (data: { email: string; password: string; full_name: string }) =>
    api.post("/auth/register", data),
  login: (data: { email: string; password: string }) =>
    api.post<{ access_token: string; refresh_token: string; token_type: string }>(
      "/auth/login",
      data
    ),
};

export const patients = {
  list: () => api.get("/patients/"),
  create: (data: { full_name: string; age?: number; notes?: string }) =>
    api.post("/patients/", data),
  get: (id: string) => api.get(`/patients/${id}`),
  update: (id: string, data: object) => api.patch(`/patients/${id}`, data),
  addCaregiver: (patientId: string, data: { caregiver_email: string; role?: string }) =>
    api.post(`/patients/${patientId}/caregivers`, data),
  listCaregivers: (patientId: string) =>
    api.get(`/patients/${patientId}/caregivers`),
  getLinkToken: (patientId: string) =>
    api.post(`/patients/${patientId}/link-token`),
  getMyLinkToken: () => api.post("/patients/me/link-token"),
};

export const medications = {
  list: (patientId: string) => api.get(`/patients/${patientId}/medications`),
  add: (patientId: string, data: object) =>
    api.post(`/patients/${patientId}/medications`, data),
  update: (medId: string, data: object) =>
    api.patch(`/medications/${medId}`, data),
  delete: (medId: string) => api.delete(`/medications/${medId}`),
};

export const prescriptions = {
  scan: (patientId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post(`/patients/${patientId}/prescriptions/scan`, form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  confirm: (patientId: string, scanId: string, data: object) =>
    api.post(`/patients/${patientId}/prescriptions/${scanId}/confirm`, data),
};
