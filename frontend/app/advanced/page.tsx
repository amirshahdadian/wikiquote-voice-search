import AdvancedShell from "@/components/advanced-shell";
import { fetchPopularAuthors } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Advanced Features — WikiQuote Voice",
};

export default async function AdvancedPage() {
  const authors = await fetchPopularAuthors(20);
  return <AdvancedShell initialAuthors={authors} />;
}
