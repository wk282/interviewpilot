import { useEffect, useState } from 'react'
import { Alert, Button, Spin } from 'antd'
import { useNavigate } from 'react-router-dom'
import { getWorkspaces } from '../api/workspaces'
import { getApiErrorMessage } from '../utils/apiError'
import { getWorkspaceHome, saveActiveWorkspace } from '../utils/workspaceStorage'

function HomeResolverPage() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  const resolveHome = () => {
    setError(null)
    getWorkspaces()
      .then((workspaces) => {
        const workspace = workspaces[0]
        if (!workspace) {
          setError('当前账号尚未关联工作空间，请联系管理员。')
          return
        }
        saveActiveWorkspace(workspace)
        navigate(getWorkspaceHome(workspace), { replace: true })
      })
      .catch((requestError) => {
        setError(getApiErrorMessage(requestError, '账号工作空间加载失败'))
      })
  }

  useEffect(resolveHome, [navigate])

  return (
    <main className="route-loading-page">
      {error ? (
        <Alert message="无法进入系统" description={error} type="error" showIcon action={<Button onClick={resolveHome}>重试</Button>} />
      ) : (
        <Spin size="large" tip="正在进入工作台" />
      )}
    </main>
  )
}

export default HomeResolverPage
