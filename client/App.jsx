import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";

import { useSession } from "./hooks/useSession.js";
import Login from "./pages/Login.jsx";
import Today from "./pages/Today.jsx";
import Practice from "./pages/Practice.jsx";
import Words from "./pages/Words.jsx";
import ImportExport from "./pages/ImportExport.jsx";
import Roots from "./pages/Roots.jsx";
import RootDetail from "./pages/RootDetail.jsx";
import Stats from "./pages/Stats.jsx";
import Settings from "./pages/Settings.jsx";
import Layout from "./components/Layout.jsx";

function Splash() {
  return <div className="flex h-dvh items-center justify-center text-slate-400">加载中…</div>;
}

function RequireAuth({ session }) {
  const location = useLocation();
  if (!session.authenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

export default function App() {
  const session = useSession();
  if (!session.ready) return <Splash />;
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/login"
          element={session.authenticated ? <Navigate to="/" replace /> : <Login onLogin={session.login} />}
        />
        <Route element={<RequireAuth session={session} />}>
          <Route element={<Layout />}>
            <Route index element={<Today />} />
            <Route path="practice" element={<Practice />} />
            <Route path="words" element={<Words />} />
            <Route path="words/import" element={<ImportExport />} />
            <Route path="roots" element={<Roots />} />
            <Route path="roots/:kind/:id" element={<RootDetail />} />
            <Route path="stats" element={<Stats />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
