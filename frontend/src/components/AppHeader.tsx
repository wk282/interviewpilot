import { LogoutOutlined } from '@ant-design/icons'
import { Avatar, Button } from 'antd'
import { useNavigate } from 'react-router-dom'
import { clearAuth, getStoredUser } from '../utils/authStorage'
import { clearActiveWorkspace } from '../utils/workspaceStorage'

function AppHeader() {
  const navigate = useNavigate()
  const user = getStoredUser()
  const avatarText = (user?.display_name?.trim() || user?.email || 'U').charAt(0).toUpperCase()

  const logout = () => {
    clearAuth()
    clearActiveWorkspace()
    navigate('/login', { replace: true })
  }

  return (
    <header className="topbar">
      <div className="topbar-brand"><span className="brand-mark small">IP</span><strong>InterviewPilot</strong></div>
      <div className="user-area">
        <Avatar className="user-avatar">{avatarText}</Avatar>
        <span>{user?.display_name ?? user?.email ?? '用户'}</span>
        <Button type="text" icon={<LogoutOutlined />} onClick={logout}>退出</Button>
      </div>
    </header>
  )
}

export default AppHeader
