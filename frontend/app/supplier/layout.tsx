"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken, getRole } from "@/lib/auth";
import { NavBar } from "@/components/nav-bar";

export default function SupplierLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();

  useEffect(() => {
    const token = getToken();
    const role = getRole();
    if (!token || role !== "SUPPLIER") {
      router.replace("/login");
    }
  }, [router]);

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>
    </div>
  );
}
