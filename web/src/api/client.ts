import axios from 'axios';
import { message } from 'antd';

const client = axios.create({
  baseURL: '',
  timeout: 30000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    } else if (status === 403) {
      message.error('权限不足');
    } else if (status && status >= 500) {
      message.error('服务器错误');
    }
    return Promise.reject(error);
  },
);

export default client;