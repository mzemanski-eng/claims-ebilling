"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { clearToken, getUserInfo, isAdmin, isCarrierRole, isSupplier } from "@/lib/auth";

export function NavBar() {
  const router = useRouter();
  const user = getUserInfo();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2">
          <span className="text-lg font-bold text-blue-700">
            Claims eBilling
          </span>
          {user?.carrier_name && (
            <span className="text-sm text-gray-400">· {user.carrier_name}</span>
          )}
          {user?.supplier_name && (
            <span className="text-sm text-gray-400">
              · {user.supplier_name}
            </span>
          )}
        </Link>

        {/* Links */}
        <div className="flex items-center gap-6 text-sm font-medium text-gray-600">
          {isSupplier() && (
            <>
              <Link
                href="/supplier/invoices"
                className="hover:text-blue-600 transition-colors"
              >
                My Invoices
              </Link>
              <Link
                href="/supplier/invoices/new"
                className="hover:text-blue-600 transition-colors"
              >
                + New Invoice
              </Link>
            </>
          )}
          {isCarrierRole() && (
            <Link
              href="/carrier/queue"
              className="hover:text-blue-600 transition-colors"
            >
              Review Queue
            </Link>
          )}
          {isAdmin() && (
            <>
              <Link
                href="/admin/invoices"
                className="hover:text-blue-600 transition-colors"
              >
                Invoice Queue
              </Link>
              <Link
                href="/admin/suppliers"
                className="hover:text-blue-600 transition-colors"
              >
                Suppliers
              </Link>
              <Link
                href="/admin/mappings"
                className="hover:text-blue-600 transition-colors"
              >
                Mappings
              </Link>
              <Link
                href="/admin/analytics"
                className="hover:text-blue-600 transition-colors"
              >
                Analytics
              </Link>
            </>
          )}

          <div className="ml-4 flex items-center gap-3 border-l pl-4">
            <span className="text-xs text-gray-400">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-200"
            >
              Log out
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
