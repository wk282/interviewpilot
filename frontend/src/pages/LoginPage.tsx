import { useState } from 'react'
import { ArrowRightOutlined, CheckCircleFilled, LockOutlined, MailOutlined } from '@ant-design/icons'
import { Button, Checkbox, Form, Input, Typography, message } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { login } from '../api/auth'
import { getApiErrorMessage } from '../utils/apiError'
import { saveAuth } from '../utils/authStorage'

interface LoginFormValues {
  email: string
  password: string
  remember?: boolean
}

function LoginPage() {
  const navigate = useNavigate()
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (values: LoginFormValues) => {
    setSubmitting(true)
    try {
      const auth = await login({ email: values.email, password: values.password })
      saveAuth(auth, values.remember ?? false)
      message.success('登录成功')
      navigate('/home', { replace: true })
    } catch (error) {
      message.error(getApiErrorMessage(error, '登录失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-showcase">
        <div className="brand-mark">IP</div>
        <div>
          <p className="eyebrow">INTERVIEWPILOT</p>
          <h1>让每一次技术面试<br />都有证据、有反馈、有成长</h1>
          <p className="showcase-copy">基于 Agentic CRAG，连接简历、岗位知识与评分标准，服务个人模拟训练与企业候选人评估。</p>
        </div>
        <div className="feature-list">
          <span><CheckCircleFilled /> 简历驱动的动态追问</span>
          <span><CheckCircleFilled /> 可溯源的回答与评分证据</span>
          <span><CheckCircleFilled /> 检索评估与生成自纠错</span>
        </div>
        <p className="showcase-footer">Candidate Practice · Enterprise Assessment</p>
      </section>

      <section className="auth-panel">
        <div className="auth-card">
          <div className="mobile-brand"><span className="brand-mark small">IP</span> InterviewPilot</div>
          <Typography.Title level={2}>欢迎回来</Typography.Title>
          <Typography.Paragraph type="secondary">登录后继续你的面试旅程</Typography.Paragraph>

          <Form<LoginFormValues> layout="vertical" size="large" onFinish={handleSubmit} requiredMark={false} initialValues={{ remember: true }}>
            <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '请输入有效邮箱' }]}>
              <Input prefix={<MailOutlined />} placeholder="name@example.com" />
            </Form.Item>
            <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }, { min: 8, message: '密码至少 8 位' }]}>
              <Input.Password prefix={<LockOutlined />} placeholder="请输入密码" />
            </Form.Item>
            <div className="form-options">
              <Form.Item name="remember" valuePropName="checked" noStyle><Checkbox>记住我</Checkbox></Form.Item>
              <Button type="link" className="text-link">忘记密码？</Button>
            </div>
            <Button type="primary" htmlType="submit" block className="primary-action" loading={submitting}>
              登录 <ArrowRightOutlined />
            </Button>
          </Form>

          <p className="auth-switch">还没有账号？<Link to="/register">立即注册</Link></p>
        </div>
      </section>
    </main>
  )
}

export default LoginPage
