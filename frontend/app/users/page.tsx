import UsersShell from "@/components/users-shell";
import { fetchUsers } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Manage Users — WikiQuote Voice",
};

export default async function UsersPage() {
  const users = await fetchUsers();
  return <UsersShell initialUsers={users} />;
}
