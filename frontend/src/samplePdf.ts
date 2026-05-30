export type SamplePdf = {
  id: string;
  name: string;
  description: string;
  downloadUrl: string;
  available: boolean;
};

export const DEFAULT_SAMPLE: SamplePdf = {
  id: "software-requirements-document",
  name: "Software Requirements Document.pdf",
  description: "Bundled sample PDF to try the upload and analysis flow.",
  downloadUrl: "/api/samples/software-requirements-document",
  available: true,
};

export async function fetchSamplePdfFile(sample: SamplePdf = DEFAULT_SAMPLE): Promise<File> {
  const response = await fetch(sample.downloadUrl);
  if (!response.ok) {
    throw new Error("Sample PDF is not available.");
  }
  const blob = await response.blob();
  return new File([blob], sample.name, { type: "application/pdf" });
}
