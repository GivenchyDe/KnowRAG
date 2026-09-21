/// <reference types="vite/client" />

declare module "*.vue" {
  import type { DefineComponent } from "vue";

  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>;
  export default component;
}

interface ImportMetaEnv {
  /** 后端接口前缀，默认 /api（开发环境经 Vite 代理转发） */
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
