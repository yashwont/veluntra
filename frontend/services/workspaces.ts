import { api } from "@/lib/api-client";
import type { Workspace } from "@/lib/types";

export const listWorkspaces = () => api<Workspace[]>("workspaces");
