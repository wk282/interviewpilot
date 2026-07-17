import { useState } from 'react'
import { ArrowLeftOutlined, ArrowRightOutlined, BankOutlined, LockOutlined, MailOutlined, UserOutlined } from '@ant-design/icons'
import { Button, Form, Input, Segmented, Typography, message } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { register } from '../api/auth'
import { getApiErrorMessage } from '../utils/apiError'
import { saveAuth } from '../utils/authStorage'

type AccountType = 'PERSONAL' | 'ORGANIZATION'

interface RegisterFormValues {
  accountType: AccountType
  displayName: string
  organizationName?: string
  email: string
  password: string
  confirmPassword: string
}

function RegisterPage() {
  const navigate = useNavigate()
  const [form] = Form.useForm<RegisterFormValues>()
  const [accountType, setAccountType] = useState<AccountType>('PERSONAL')
  const [submitting, setSubmitting] = useState(false)

  const handleAccountTypeChange = (value: string | number) => {
    const nextType = value as AccountType
    setAccountType(nextType)
    form.setFieldValue('accountType', nextType)
    if (nextType === 'PERSONAL') form.setFieldValue('organizationName', undefined)
  }

  const handleSubmit = async (values: RegisterFormValues) => {
    setSubmitting(true)
    try {
      const auth = await register({
        display_name: values.displayName,
        email: values.email,
        password: values.password,
        account_type: values.accountType,
        organization_name: values.organizationName,
      })
      saveAuth(auth)
      message.success(values.accountType === 'PERSONAL' ? '个人账号注册成功' : '企业账号注册成功')
      navigate('/home', { replace: true })
    } catch (error) {
      message.error(getApiErrorMessage(error, '注册失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="simple-page">
      <section className="simple-card register-card">
        <Link to="/login" className="back-link"><ArrowLeftOutlined /> 返回登录</Link>
        <div className="mobile-brand visible"><span className="brand-mark small">IP</span> InterviewPilot</div>
        <Typography.Title level={2}>创建账号</Typography.Title>
        <Typography.Paragraph type="secondary">
          {accountType === 'PERSONAL' ? '用于个人模拟面试与学习提升' : '用于企业招聘与候选人评估'}
        </Typography.Paragraph>

        <Form<RegisterFormValues>
          form={form}
          layout="vertical"
          size="large"
          onFinish={handleSubmit}
          requiredMark={false}
          initialValues={{ accountType: 'PERSONAL' }}
        >
          <Form.Item label="账号类型" name="accountType">
            <Segmented
              block
              options={[
                { label: '个人用户', value: 'PERSONAL', icon: <UserOutlined /> },
                { label: '企业管理员', value: 'ORGANIZATION', icon: <BankOutlined /> },
              ]}
              onChange={handleAccountTypeChange}
            />
          </Form.Item>

          {accountType === 'ORGANIZATION' && (
            <Form.Item label="企业名称" name="organizationName" rules={[{ required: true, message: '请输入企业名称' }, { min: 2, message: '企业名称至少 2 个字符' }]}>
              <Input prefix={<BankOutlined />} placeholder="企业或招聘团队名称" />
            </Form.Item>
          )}

          <Form.Item label={accountType === 'PERSONAL' ? '显示名称' : '管理员姓名'} name="displayName" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input prefix={<UserOutlined />} placeholder="你的名字" />
          </Form.Item>
          <Form.Item label="邮箱" name="email" rules={[{ required: true, message: '请输入邮箱' }, { type: 'email', message: '请输入有效邮箱' }]}>
            <Input prefix={<MailOutlined />} placeholder="name@example.com" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码' }, { min: 8, message: '密码至少 8 位' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
          </Form.Item>
          <Form.Item
            label="确认密码"
            name="confirmPassword"
            dependencies={['password']}
            rules={[
              { required: true, message: '请再次输入密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  return !value || getFieldValue('password') === value
                    ? Promise.resolve()
                    : Promise.reject(new Error('两次密码输入不一致'))
                },
              }),
            ]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="再次输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block className="primary-action" loading={submitting}>
            {accountType === 'PERSONAL' ? '创建个人账号' : '创建企业空间'} <ArrowRightOutlined />
          </Button>
        </Form>
        <p className="auth-switch">已有账号？<Link to="/login">返回登录</Link></p>
      </section>
    </main>
  )
}

export default RegisterPage
