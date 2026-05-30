/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SECURE_DEPLOYMENT?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
