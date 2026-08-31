import { apiFetch } from "@/lib/api/client";

// Real, unsandboxed access to a folder on this machine (services/host-runner) — same shape as
// lib/api/workspace.ts's isolated equivalent, but every path here is relative to HOST_ROOT on the
// real disk, not a tenant-scoped sandbox. See docs/architecture/coding-agent.md.
export interface HostEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size_bytes: number | null;
}

export interface HostFile {
  path: string;
  content: string;
}

export async function listHostFiles(dir: string = "."): Promise<HostEntry[]> {
  return apiFetch<HostEntry[]>(`/host/files?path=${encodeURIComponent(dir)}`);
}

export async function getHostFileContent(path: string): Promise<HostFile> {
  return apiFetch<HostFile>(`/host/files/content?path=${encodeURIComponent(path)}`);
}

export async function uploadHostFile(path: string, file: File): Promise<HostFile> {
  const formData = new FormData();
  formData.append("file", file);
  return apiFetch<HostFile>(`/host/files?path=${encodeURIComponent(path)}`, {
    method: "POST",
    body: formData,
  });
}

export async function deleteHostFile(path: string): Promise<void> {
  return apiFetch<void>(`/host/files?path=${encodeURIComponent(path)}`, { method: "DELETE" });
}
