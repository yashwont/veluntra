import { api, sessionRequest } from "@/lib/api-client";
import type { User } from "@/lib/types";

export const login = (email: string, password: string) =>
  sessionRequest("login", { email, password });

export const register = (email: string, password: string, fullName: string) =>
  sessionRequest("register", { email, password, full_name: fullName });

export const logout = () => sessionRequest("logout");

export const getMe = () => api<User>("users/me");
