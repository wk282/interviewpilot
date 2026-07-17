import { useEffect, useState } from 'react'
import { BankOutlined, LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Form, Input, Spin, Tag, Typography, message } from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { acceptInvitation, getInvitation } from '../api/invitations'
import type { InvitationAcceptRequest, InvitationInfo } from '../types/invitation'
import { getApiErrorMessage } from '../utils/apiError'
import { saveAuth } from '../utils/authStorage'

interface AcceptFormValues extends InvitationAcceptRequest {
  confirmPassword: string
}

function InvitationAcceptPage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const [invitation, setInvitation] = useState<InvitationInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getInvitation(token)
      .then(setInvitation)
      .catch((requestError) => setError(getApiErrorMessage(requestError, '邀请加载失败')))
      .finally(() => setLoading(false))
  }, [token])

  const submit = async (values: AcceptFormValues) => {
    setSubmitting(true)
    try {
      const auth = await acceptInvitation(token, { display_name: values.display_name, password: values.password })
      saveAuth(auth)
      message.success('企业账号创建成功')
      navigate('/home', { replace: true })
    } catch (requestError) {
      message.error(getApiErrorMessage(requestError, '接受邀请失败'))
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <main className="route-loading-page"><Spin size="large" /></main>
  if (error || !invitation) {
    return <main className="route-loading-page"><Alert type="error" showIcon message="无法接受邀请" description={error ?? '邀请不存在'} action={<Link to="/login">返回登录</Link>} /></main>
  }

  return (
    <main className="simple-page">
      <section className="simple-card invitation-card">
        <div className="mobile-brand visible"><span className="brand-mark small">IP</span> InterviewPilot</div>
        <div className="invitation-company-icon"><BankOutlined /></div>
        <Typography.Title level={2}>加入 {invitation.workspace_name}</Typography.Title>
        <Typography.Paragraph type="secondary">受邀邮箱：{invitation.email}</Typography.Paragraph>
        <Tag color="blue">角色：{invitation.role}</Tag>

        <Form<AcceptFormValues> className="invitation-form" layout="vertical" size="large" onFinish={submit} requiredMark={false}>
          <Form.Item label="姓名" name="display_name" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input prefix={<UserOutlined />} placeholder="你的名字" />
          </Form.Item>
          <Form.Item label="设置密码" name="password" rules={[{ required: true, message: '请输入密码' }, { min: 8, message: '密码至少 8 位' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({ validator(_, value) { return !value || getFieldValue('password') === value ? Promise.resolve() : Promise.reject(new Error('两次密码输入不一致')) } }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="再次输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={submitting} block>接受邀请并创建账号</Button>
        </Form>
      </section>
    </main>
  )
}

export default InvitationAcceptPage
