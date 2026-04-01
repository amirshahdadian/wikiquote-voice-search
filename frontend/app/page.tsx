import LandingShell from "@/components/landing-shell";
import { fetchRandomQuote, fetchUsers } from "@/lib/api";

export default async function LandingPage() {
  const [users, featuredQuote] = await Promise.all([fetchUsers(), fetchRandomQuote()]);

  return <LandingShell featuredQuote={featuredQuote} users={users} />;
}
