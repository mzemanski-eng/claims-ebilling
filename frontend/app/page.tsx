"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken, getRole } from "@/lib/auth";

/** Root — redirect to dashboard based on role, or to login if unauthenticated. */
export default function RootPage() {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    const role = getRole();

    if (!token) {
      router.replace("/login");
      return;
    }

    if (role === "SUPPLIER") {
      router.replace("/supplier/invoices");
    } else if (role === "CARRIER_ADMIN" || role === "CARRIER_REVIEWER") {
      router.replace("/carrier/queue");
    } else {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-gray-500">Redirecting…</p>
    </div>
  );
}
