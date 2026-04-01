import { Suspense } from "react";

import InteractionShell from "@/components/interaction-shell";
import { fetchUsers } from "@/lib/api";

export default async function AppPage() {
  const users = await fetchUsers();

  return (
    <Suspense
      fallback={
        <main className="mx-auto flex min-h-screen w-full max-w-7xl items-center justify-center px-6 py-10 text-fog">
          Loading the interaction interface...
        </main>
      }
    >
      <InteractionShell initialUsers={users} />
    </Suspense>
  );
}
