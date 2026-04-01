import ProfileShell from "@/components/profile-shell";
import { fetchUsers } from "@/lib/api";

export default async function ProfilePage() {
  const users = await fetchUsers();

  return <ProfileShell initialUsers={users} />;
}
