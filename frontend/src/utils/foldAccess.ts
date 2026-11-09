import type { AuthUser } from '@/stores/auth'

/** 普通用户只能看到自己的任务，因此可以管理列表里的每一条。管理员只管理自己提交的。 */
export function canManageFoldTask(
  user: AuthUser | null | undefined,
  ownerUsername?: string | null,
) {
  if (!user?.is_admin) return true
  return !!ownerUsername && ownerUsername === user.username
}
