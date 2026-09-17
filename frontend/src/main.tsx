import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { createRouter, RouterProvider } from "@tanstack/react-router"
import { StrictMode } from "react"
import ReactDOM from "react-dom/client"
import { ApiError, OpenAPI } from "./client"
import { ThemeProvider } from "./components/theme-provider"
import { Toaster } from "./components/ui/sonner"
import "./index.css"
import { routeTree } from "./routeTree.gen"

// API 基地址留空 = 使用"同源相对路径"。
//
// 为什么不用 VITE_API_URL：
//   1. 该变量在 `bun run build` 时被**烤进产物**，产物从此绑定那个地址 ——
//      换个主机/端口跑就失效，无法分发。
//   2. 生产形态下前端由后端托管（同源），根本不需要绝对地址；
//      开发时由 vite.config 的 proxy 转发，浏览器看到的同样是同源。
// 留空后 OpenAPI 客户端会发 `/api/v1/...`，两种形态都对。
OpenAPI.BASE = ""
OpenAPI.TOKEN = async () => {
  return localStorage.getItem("access_token") || ""
}

const handleApiError = (error: Error) => {
  if (error instanceof ApiError && [401, 403].includes(error.status)) {
    localStorage.removeItem("access_token")
    window.location.href = "/login"
  }
}
const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: handleApiError,
  }),
  mutationCache: new MutationCache({
    onError: handleApiError,
  }),
})

const router = createRouter({ routeTree })
declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
