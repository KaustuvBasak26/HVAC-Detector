export type SamplePdf = {
  id: string;
  name: string;
  description: string;
  downloadUrl: string;
  available: boolean;
};

export const DEFAULT_SAMPLE: SamplePdf = {
  id: "testset2",
  name: "testset2.pdf",
  description: "Mechanical HVAC floor plan bundled with the project for demo duct detection.",
  downloadUrl: "/api/samples/testset2",
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

export type UploadLimits = {
  maxUploadSizeMb: number;
  demoMode: boolean;
  lowMemoryMode: boolean;
};

export async function fetchUploadLimits(): Promise<UploadLimits> {
  const response = await fetch("/api/samples");
  if (!response.ok) {
    return { maxUploadSizeMb: 100, demoMode: false, lowMemoryMode: false };
  }
  const body = (await response.json()) as Partial<UploadLimits>;
  return {
    maxUploadSizeMb: typeof body.maxUploadSizeMb === "number" ? body.maxUploadSizeMb : 100,
    demoMode: Boolean(body.demoMode),
    lowMemoryMode: Boolean(body.lowMemoryMode),
  };
}
