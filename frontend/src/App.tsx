import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './store/auth'
import SignUp from './pages/SignUp'
import Login from './pages/Login'
import OAuthAuthorize from './pages/OAuthAuthorize'
import Dashboard from './pages/Dashboard'
import Wishlist from './pages/Wishlist'
import SocialGraph from './pages/SocialGraph'
import Purchases from './pages/Purchases'
import Profile from './pages/Profile'
import FriendProfile from './pages/FriendProfile'
import AgentFeed from './pages/AgentFeed'
import Layout from './components/Layout'

export default function App() {
  const agentId = useAuthStore((s) => s.agentId)

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/signup" element={<SignUp />} />
        <Route path="/login" element={<Login />} />
        <Route path="/oauth/authorize" element={<OAuthAuthorize />} />
        {agentId ? (
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/wishlist" element={<Wishlist />} />
            <Route path="/social" element={<SocialGraph />} />
            <Route path="/purchases" element={<Purchases />} />
            <Route path="/profile" element={<Profile />} />
            <Route path="/social/profile/:agentId" element={<FriendProfile />} />
            <Route path="/feed" element={<AgentFeed />} />
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" replace />} />
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
