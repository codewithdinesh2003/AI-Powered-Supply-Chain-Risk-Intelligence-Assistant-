import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Zap, Eye, EyeOff, AlertCircle } from 'lucide-react'
import { Spinner } from '../components/ui/Spinner'
import { authApi } from '../api/client'
import { useStore } from '../store/useStore'

export default function Login() {
  const navigate = useNavigate()
  const { setUser, setAccessToken } = useStore((s) => ({
    setUser: s.setUser,
    setAccessToken: s.setAccessToken,
  }))

  const [email, setEmail] = useState('admin@scm-intel.local')
  const [password, setPassword] = useState('Admin@123')
  const [showPwd, setShowPwd] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const tokens = await authApi.login(email, password)
      setAccessToken(tokens.access_token)
      const user = await authApi.me()
      setUser(user)
      navigate('/', { replace: true })
    } catch {
      setError('Invalid email or password. Try admin@scm-intel.local / Admin@123')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-navy-900 flex items-center justify-center p-4">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: 'linear-gradient(#1E6FD9 1px, transparent 1px), linear-gradient(to right, #1E6FD9 1px, transparent 1px)',
          backgroundSize: '40px 40px',
        }}
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="relative w-full max-w-md"
      >
        {/* Brand */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-accent-blue mb-4 shadow-lg">
            <Zap size={28} className="text-white" />
          </div>
          <h1 className="text-white text-2xl font-bold tracking-wide font-mono">
            SCM<span className="text-accent-blue">·</span>INTEL
          </h1>
          <p className="text-navy-400 text-sm mt-1">Supply Chain Risk Intelligence</p>
        </div>

        {/* Card */}
        <div className="bg-navy-800 border border-navy-600 rounded-2xl p-8 shadow-2xl">
          <h2 className="text-white font-semibold text-lg mb-6">Sign in to your workspace</h2>

          {error && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="flex items-start gap-2 bg-red-950 border border-red-800 text-red-300 rounded-lg px-4 py-3 mb-4 text-sm"
            >
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              {error}
            </motion.div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-navy-300 text-sm font-medium mb-1.5">Email address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full bg-navy-900 border border-navy-600 text-white placeholder-navy-400 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent-blue focus:border-transparent transition-all"
                placeholder="you@company.com"
              />
            </div>

            <div>
              <label className="block text-navy-300 text-sm font-medium mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPwd ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full bg-navy-900 border border-navy-600 text-white placeholder-navy-400 rounded-lg px-4 py-2.5 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-accent-blue focus:border-transparent transition-all"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPwd(!showPwd)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-navy-400 hover:text-white transition-colors"
                >
                  {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent-blue hover:bg-accent-blue-light disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 mt-2"
            >
              {loading ? <Spinner size="sm" /> : null}
              {loading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="text-navy-500 text-xs text-center mt-6">
            Default credentials: admin@scm-intel.local / Admin@123
          </p>
        </div>
      </motion.div>
    </div>
  )
}
