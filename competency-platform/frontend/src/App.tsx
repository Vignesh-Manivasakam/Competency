/**
 * Root application component with React Router.
 * From §10.1: React 18 SPA with TanStack Query provider.
 * From §10.2 / §10.3: Manager and Employee portal routes.
 */
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { AppShell } from "@/components/layout/AppShell";

// Manager pages
import Dashboard from "@/pages/manager/Dashboard";
import Competencies from "@/pages/manager/Competencies";
import CompetencyWizard from "@/pages/manager/CompetencyWizard";
import CompetencyDetail from "@/pages/manager/CompetencyDetail";
import Employees from "@/pages/manager/Employees";
import EmployeeDetail from "@/pages/manager/EmployeeDetail";
import Reviews from "@/pages/manager/Reviews";

// Employee pages
import MyLearning from "@/pages/employee/MyLearning";
import EmployeeCompetencyDetail from "@/pages/employee/CompetencyDetail";
import LearningSession from "@/pages/employee/LearningSession";
import SessionComplete from "@/pages/employee/SessionComplete";
import MyProfile from "@/pages/employee/MyProfile";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,        // 30s before refetch
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Main App Layout Shell — protected by AppShell auth gate */}
          <Route element={<AppShell />}>
            {/* Manager routes */}
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/competencies" element={<Competencies />} />
            <Route path="/competencies/new" element={<CompetencyWizard />} />
            <Route path="/competencies/:id" element={<CompetencyDetail />} />
            <Route path="/employees" element={<Employees />} />
            <Route path="/employees/:id" element={<EmployeeDetail />} />
            <Route path="/reviews" element={<Reviews />} />

            {/* Employee routes with sidebar layout */}
            <Route path="/my-learning" element={<MyLearning />} />
            <Route path="/my-learning/:competencyId" element={<EmployeeCompetencyDetail />} />
            <Route path="/sessions/:id/complete" element={<SessionComplete />} />
            <Route path="/my-profile" element={<MyProfile />} />
          </Route>

          {/* Full-screen Learning Session — NO sidebar layout wrapper per §10.3 */}
          <Route path="/sessions/:id" element={<LearningSession />} />

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />

          {/* Login fallback */}
          <Route path="/login" element={<div className="flex h-screen items-center justify-center text-muted-foreground">Login Page</div>} />
        </Routes>
      </BrowserRouter>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
