import MainShell from "@/components/main-shell";
import { fetchUsers } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Page() {
  const users = await fetchUsers();
  return <MainShell initialUsers={users} />;
}
