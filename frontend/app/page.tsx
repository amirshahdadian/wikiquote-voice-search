import MainShell from "@/components/main-shell";
import { fetchRandomQuote, fetchUsers } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Page() {
  const [users, randomQuote] = await Promise.all([
    fetchUsers(),
    fetchRandomQuote(),
  ]);

  return <MainShell initialUsers={users} initialQuote={randomQuote} />;
}
