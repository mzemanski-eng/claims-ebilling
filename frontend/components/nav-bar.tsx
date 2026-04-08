"use client";

import Link from "next/link";
import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getUserInfo, isAdmin, isCarrierAdmin, isCarrierRole, isSupplier } from "@/lib/auth";

// ── Nav structure ──────────────────────────────────────────────────────────────

type NavLink  = { type: "link";  href: string; label: string; exact?: boolean };
type NavGroup = { type: "group"; label: string; items: { href: string; label: string }[] };
type NavItem  = NavLink | NavGroup;

/** Full admin nav — CARRIER_ADMIN and SYSTEM_ADMIN */
const ADMIN_NAV: NavItem[] = [
  { type: "link",  href: "/admin",           label: "Dashboard", exact: true },
  { type: "group", label: "Invoices", items: [
    { href: "/admin/invoices",          label: "Invoice Queue" },
    { href: "/carrier/queue",           label: "Review Queue" },
    { href: "/carrier/classification",  label: "Classification Queue" },
    { href: "/admin/mappings",          label: "Mapping Rules" },
  ]},
  { type: "group", label: "Operations", items: [
    { href: "/admin/suppliers", label: "Suppliers" },
    { href: "/admin/contracts", label: "Contracts" },
    { href: "/admin/team",      label: "Team" },
  ]},
  { type: "link",  href: "/admin/analytics", label: "Analytics" },
  { type: "link",  href: "/admin/settings",  label: "Settings"  },
];

/** Focused auditor nav — CARRIER_REVIEWER only */
const REVIEWER_NAV: NavItem[] = [
  { type: "link",  href: "/admin",          label: "Dashboard", exact: true },
  { type: "group", label: "Invoices", items: [
    { href: "/carrier/queue",           label: "Review Queue" },
    { href: "/carrier/classification",  label: "Classification Queue" },
  ]},
];

// ── Helpers ────────────────────────────────────────────────────────────────────

const linkCls = (active: boolean) =>
  `rounded px-3 py-1.5 text-sm transition-colors ${
    active
      ? "bg-blue-50 text-blue-700 font-semibold"
      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
  }`;

// ── NavBar ─────────────────────────────────────────────────────────────────────

export function NavBar() {
  const router   = useRouter();
  const pathname = usePathname();
  const user     = getUserInfo();
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  function isActive(href: string, exact?: boolean): boolean {
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  }

  function groupIsActive(items: { href: string }[]): boolean {
    return items.some((i) => pathname.startsWith(i.href));
  }

  const adminNav = isCarrierRole() && !isCarrierAdmin() ? REVIEWER_NAV : ADMIN_NAV;

  return (
    <nav className="border-b bg-white shadow-sm">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">

        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <span className="text-lg font-bold text-blue-700">Claims eBilling</span>
          {user?.carrier_name && (
            <span className="text-sm text-gray-400">· {user.carrier_name}</span>
          )}
          {user?.supplier_name && (
            <span className="text-sm text-gray-400">· {user.supplier_name}</span>
          )}
        </Link>

        {/* Links */}
        <div className="flex items-center gap-1">

          {/* Supplier nav */}
          {isSupplier() && (
            <>
              <Link href="/supplier" className={linkCls(isActive("/supplier", true))}>
                Dashboard
              </Link>
              <Link href="/supplier/invoices" className={linkCls(isActive("/supplier/invoices"))}>
                My Invoices
              </Link>
              <Link href="/supplier/invoices/new" className={linkCls(isActive("/supplier/invoices/new"))}>
                + New Invoice
              </Link>
            </>
          )}

          {/* Carrier / admin nav */}
          {isAdmin() && adminNav.map((item) => {
            if (item.type === "link") {
              return (
                <Link key={item.href} href={item.href} className={linkCls(isActive(item.href, item.exact))}>
                  {item.label}
                </Link>
              );
            }

            // Dropdown group
            const active = groupIsActive(item.items);
            const open   = openGroup === item.label;
            return (
              <div
                key={item.label}
                className="relative"
                onMouseEnter={() => setOpenGroup(item.label)}
                onMouseLeave={() => setOpenGroup(null)}
              >
                <button
                  className={`flex items-center gap-1 rounded px-3 py-1.5 text-sm transition-colors ${
                    active
                      ? "bg-blue-50 text-blue-700 font-semibold"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                  }`}
                >
                  {item.label}
                  <svg
                    className={`h-3 w-3 transition-transform ${open ? "rotate-180" : ""}`}
                    fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {open && (
                  <div className="absolute left-0 top-full z-50 mt-1 w-48 rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
                    {item.items.map((sub) => (
                      <Link
                        key={sub.href}
                        href={sub.href}
                        onClick={() => setOpenGroup(null)}
                        className={`block px-4 py-2 text-sm transition-colors ${
                          isActive(sub.href)
                            ? "bg-blue-50 text-blue-700 font-semibold"
                            : "text-gray-700 hover:bg-gray-50 hover:text-gray-900"
                        }`}
                      >
                        {sub.label}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {/* User strip */}
          <div className="ml-3 flex items-center gap-3 border-l pl-4">
            {user?.role && (
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                user.role === "CARRIER_REVIEWER" ? "bg-blue-50 text-blue-600"
                : user.role === "CARRIER_ADMIN"  ? "bg-violet-50 text-violet-600"
                : user.role === "SYSTEM_ADMIN"   ? "bg-red-50 text-red-600"
                : "bg-gray-100 text-gray-500"
              }`}>
                {user.role === "CARRIER_REVIEWER" ? "Auditor"
                  : user.role === "CARRIER_ADMIN" ? "Admin"
                  : user.role === "SYSTEM_ADMIN"  ? "System"
                  : "Supplier"}
              </span>
            )}
            <span className="text-xs text-gray-400">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-200 transition-colors"
            >
              Log out
            </button>
          </div>
        </div>

      </div>
    </nav>
  );
}
