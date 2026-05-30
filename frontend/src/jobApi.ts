export function jobViewerHeaders(viewerToken: string | null): HeadersInit {
  if (!viewerToken) return {};
  return { "X-Job-Viewer-Token": viewerToken };
}
