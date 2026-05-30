import { secureDeployment } from "./secureDeployment";

export function jobViewerHeaders(viewerToken: string | null): HeadersInit {
  if (!viewerToken) return {};
  return { "X-Job-Viewer-Token": viewerToken };
}

export function clearDemoSession(jobId: string | null): void {
  if (!secureDeployment || !jobId) return;
  sessionStorage.removeItem(`job-viewer:${jobId}`);
}

export async function releaseDemoJob(jobId: string, viewerToken: string | null): Promise<void> {
  if (!secureDeployment) return;
  await fetch(`/api/jobs/${jobId}/release`, {
    method: "POST",
    headers: jobViewerHeaders(viewerToken),
  });
}
