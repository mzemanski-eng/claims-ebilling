"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Admin root — redirect straight to the invoice queue. */
export default function AdminPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/invoices");
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gray-500">Redirecting…</p>
    </div>
  );
}
