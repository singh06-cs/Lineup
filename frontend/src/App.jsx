import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import { AuthProvider } from './auth/AuthContext'
import RequireAuth from './auth/RequireAuth'
import Layout from './components/Layout'
import AccountPage from './pages/AccountPage'
import DashboardPage from './pages/DashboardPage'
import LoginPage from './pages/LoginPage'
import OrganizationPage from './pages/OrganizationPage'
import RegisterPage from './pages/RegisterPage'
import SchedulePage from './pages/SchedulePage'
import ShiftsPage from './pages/ShiftsPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route index element={<DashboardPage />} />
              <Route path="orgs/:orgId" element={<OrganizationPage />} />
              <Route path="shifts" element={<ShiftsPage />} />
              <Route path="schedule" element={<SchedulePage />} />
              <Route path="account" element={<AccountPage />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
