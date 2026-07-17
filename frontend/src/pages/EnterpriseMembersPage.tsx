import { useEffect, useState } from 'react'
import { CopyOutlined, PlusOutlined } from '@ant-design/icons'
import { Alert, Avatar, Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { createWorkspaceInvitation, getWorkspaceMembers } from '../api/invitations'
import AppHeader from '../components/AppHeader'
import EnterpriseSidebar from '../components/EnterpriseSidebar'
import type { InvitationCreateRequest, WorkspaceMember } from '../types/invitation'
import { getApiErrorMessage } from '../utils/apiError'
import { getActiveWorkspace } from '../utils/workspaceStorage'

const roleLabels: Record<string, string> = {
  OWNER: '所有者',
  ADMIN: '管理员',
  HR: 'HR',
  INTERVIEWER: '面试官',
  VIEWER: '只读成员',
}

function EnterpriseMembersPage() {
  const workspace = getActiveWorkspace()
  const [form] = Form.useForm<InvitationCreateRequest>()
  const [members, setMembers] = useState<WorkspaceMember[]>([])
  const [loading, setLoading] = useState(true)
  const [inviting, setInviting] = useState(false)
  const [inviteOpen, setInviteOpen] = useState(false)
  const [invitationLink, setInvitationLink] = useState<string | null>(null)

  const loadMembers = () => {
    if (!workspace) return
    setLoading(true)
    getWorkspaceMembers(workspace.id)
      .then(setMembers)
      .catch((error) => message.error(getApiErrorMessage(error, '成员列表加载失败')))
      .finally(() => setLoading(false))
  }

  useEffect(loadMembers, [workspace?.id])

  const submitInvitation = async (values: InvitationCreateRequest) => {
    if (!workspace) return
    setInviting(true)
    try {
      const invitation = await createWorkspaceInvitation(workspace.id, values)
      setInvitationLink(`${window.location.origin}/invitations/${invitation.invitation_token}`)
      form.resetFields()
    } catch (error) {
      message.error(getApiErrorMessage(error, '邀请创建失败'))
    } finally {
      setInviting(false)
    }
  }

  const copyInvitation = async () => {
    if (!invitationLink) return
    await navigator.clipboard.writeText(invitationLink)
    message.success('邀请链接已复制')
  }

  const closeInvitation = () => {
    setInviteOpen(false)
    setInvitationLink(null)
    form.resetFields()
  }

  const columns: ColumnsType<WorkspaceMember> = [
    {
      title: '成员',
      key: 'member',
      render: (_, member) => (
        <div className="member-identity">
          <Avatar>{(member.display_name || member.email).charAt(0).toUpperCase()}</Avatar>
          <div><strong>{member.display_name || '未设置姓名'}</strong><span>{member.email}</span></div>
        </div>
      ),
    },
    { title: '角色', dataIndex: 'role', key: 'role', render: (role) => <Tag color={role === 'OWNER' ? 'purple' : 'blue'}>{roleLabels[role] ?? role}</Tag> },
    { title: '加入时间', dataIndex: 'joined_at', key: 'joined_at', render: (value) => new Date(value).toLocaleString('zh-CN') },
  ]

  return (
    <main className="dashboard-page">
      <AppHeader />
      <div className="dashboard-shell">
        <EnterpriseSidebar workspace={workspace} />
        <section className="dashboard-main">
          <div className="dashboard-welcome">
            <div>
              <p className="eyebrow dark">MEMBERS</p>
              <Typography.Title level={2}>成员管理</Typography.Title>
              <Typography.Paragraph type="secondary">{members.length} 名企业成员</Typography.Paragraph>
            </div>
            <Button type="primary" size="large" icon={<PlusOutlined />} onClick={() => setInviteOpen(true)}>邀请成员</Button>
          </div>

          <section className="content-panel member-panel">
            <Table rowKey="user_id" columns={columns} dataSource={members} loading={loading} pagination={false} scroll={{ x: 620 }} />
          </section>
        </section>
      </div>

      <Modal title="邀请企业成员" open={inviteOpen} onCancel={closeInvitation} footer={null} destroyOnHidden>
        {invitationLink ? (
          <Space direction="vertical" size="middle" className="invite-result">
            <Alert type="success" showIcon message="邀请已创建" description="该链接有效期为 7 天，只能使用一次。" />
            <Input.TextArea value={invitationLink} readOnly autoSize={{ minRows: 2, maxRows: 4 }} />
            <Button type="primary" icon={<CopyOutlined />} onClick={copyInvitation} block>复制邀请链接</Button>
          </Space>
        ) : (
          <Form<InvitationCreateRequest> form={form} layout="vertical" onFinish={submitInvitation} requiredMark={false} initialValues={{ role: 'HR' }}>
            <Form.Item label="企业邮箱" name="email" rules={[{ required: true, message: '请输入员工邮箱' }, { type: 'email', message: '请输入有效邮箱' }]}>
              <Input placeholder="employee@company.com" />
            </Form.Item>
            <Form.Item label="角色" name="role" rules={[{ required: true }]}>
              <Select options={[
                { value: 'ADMIN', label: '管理员' },
                { value: 'HR', label: 'HR' },
                { value: 'INTERVIEWER', label: '面试官' },
                { value: 'VIEWER', label: '只读成员' },
              ]} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={inviting} block>生成邀请链接</Button>
          </Form>
        )}
      </Modal>
    </main>
  )
}

export default EnterpriseMembersPage
