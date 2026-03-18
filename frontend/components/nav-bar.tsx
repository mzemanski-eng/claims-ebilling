"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getUserInfo, isAdmin, isCarrierRole, isSupplier } from "@/lib/auth";

// ── Admin nav link definitions ─────────────────────────────────────────────────
// exact: true means only highlight when path matches exactly (not prefix)

const ADMIN_LINKS: { href: string; label: string; exact?: boolean }[] = [
  { href: "/admin",           label: "Dashboard",     exact: true },
  { href: "/admin/invoices",  label: "Invoice Queue" },
  { href: "/admin/suppliers", label: "Suppliers" },
  { href: "/admin/contracts", label: "Contracts" },
  { href: "/admin/mappings",  label: "Mappings" },
  { href: "/admin/analytics", label: "Analytics" },
  { href: "/admin/team",      label: "Team" },
];

// ── NavLink helper ─────────────────────────────────────────────────────────────

function NavLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded px-3 py-1.5 text-sm transition-colors ${
        active
          ? "bg-blue-50 text-blue-700 font-semibold"
          : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
      }`}
    >
      {children}
    </Link>
  );
}

// ── NavBar ─────────────────────────────────────────────────────────────────────

export function NavBar() {
  const router = useRouter();
  const pathname = usePathname();
  const user = getUserInfo();

  function handleLogout() {
    clearToken();
    router.push("/login");
  }

  /** True when this link should be highlighted as active. */
  function isActive(href: string, exact?: boolean): boolean {
    if (exact) return pathname === href;
    return pathname.startsWith(href);
  }

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
          {isSupplier() && (
            <>
              <NavLink href="/supplier/invoices" active={isActive("/supplier/invoices", true)}>
                My Invoices
              </NavLink>
              <NavLink href="/supplier/invoices/new" active={isActive("/supplier/invoices/new")}>
                + New Invoice
              </NavLink>
            </>
          )}

          {isCarrierRole() && (
            <NavLink href="/carrier/queue" active={isActive("/carrier/queue")}>
              Review Queue
            </NavLink>
          )}

          {isAdmin() &&
            ADMIN_LINKS.map((link) => (
              <NavLink
                key={link.href}
                href={link.href}
                active={isActive(link.href, link.exact)}
              >
                {link.label}
              </NavLink>
            ))}

          <div className="ml-3 flex items-center gap-3 border-l pl-4">
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
