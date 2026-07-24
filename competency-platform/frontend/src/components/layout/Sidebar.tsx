/**
 * Navigation sidebar — supports both Manager and Employee portals.
 * From §10.2 / §10.3.
 */
import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  BookOpen,
  Users,
  ClipboardCheck,
  GraduationCap,
  UserCircle,
  LogOut,
} from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const MANAGER_NAV = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/competencies", label: "Competencies", icon: BookOpen },
  { to: "/employees", label: "Employees", icon: Users },
  { to: "/reviews", label: "Reviews", icon: ClipboardCheck },
] as const;

const EMPLOYEE_NAV = [
  { to: "/my-learning", label: "My Learning", icon: GraduationCap },
  { to: "/my-profile", label: "My Profile", icon: UserCircle },
] as const;

export function Sidebar() {
  const { user, logout } = useAuthStore();
  const isEmployee = user?.role === "employee";
  const navItems = isEmployee ? EMPLOYEE_NAV : MANAGER_NAV;

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-card">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 border-b px-6">
        <BookOpen className="h-6 w-6 text-primary" />
        <span className="text-lg font-semibold tracking-tight">Competency AI</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User section */}
      <div className="border-t p-4">
        <div className="mb-2 text-sm">
          <p className="font-medium truncate">{user?.full_name ?? "User"}</p>
          <p className="text-xs text-muted-foreground capitalize">{user?.role ?? "guest"}</p>
        </div>
        <Button variant="ghost" size="sm" className="w-full justify-start text-muted-foreground hover:text-foreground" onClick={logout}>
          <LogOut className="mr-2 h-4 w-4" />
          Sign Out
        </Button>
      </div>
    </aside>
  );
}
