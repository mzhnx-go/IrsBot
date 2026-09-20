// Note: the `PrivateService` is only available when generating the client
// for local environments
import { OpenAPI, PrivateService } from "../../src/client"

// 前端已改走同源相对路径（.env 里刻意移除了 VITE_API_URL），
// Node 里的测试客户端没有"同源"概念，显式指向 vite dev（代理转发 /api → 后端）
OpenAPI.BASE = process.env.VITE_API_URL || "http://localhost:5173"

export const createUser = async ({
  email,
  password,
}: {
  email: string
  password: string
}) => {
  return await PrivateService.createUser({
    requestBody: {
      email,
      password,
      is_verified: true,
      full_name: "Test User",
    },
  })
}
