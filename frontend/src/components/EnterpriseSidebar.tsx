import { AuditOutlined, BankOutlined, BookOutlined, FileSearchOutlined, MailOutlined, SettingOutlined, SolutionOutlined, TeamOutlined } from '@ant-design/icons'
import { NavLink } from 'react-router-dom'
import type { WorkspaceSummary } from '../types/workspace'

const managementRoles = new Set(['OWNER', 'ADMIN'])
const recruitmentRoles = new Set(['OWNER', 'ADMIN', 'HR'])

function EnterpriseSidebar({ workspace }: { workspace: WorkspaceSummary | null }) {
  const role = workspace?.role ?? 'VIEWER'

  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-title"><BankOutlined /> {workspace?.name ?? '企业工作台'}</div>
      <NavLink to="/enterprise/dashboard" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><AuditOutlined /> 概览</NavLink>
      {recruitmentRoles.has(role) && <NavLink to="/enterprise/interviews" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><SolutionOutlined /> 岗位与候选人</NavLink>}
      {recruitmentRoles.has(role) && <NavLink to="/enterprise/applications" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><FileSearchOutlined /> 岗位申请</NavLink>}
      {!recruitmentRoles.has(role) && <NavLink to="/enterprise/interviews" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><FileSearchOutlined /> 面试任务</NavLink>}
      <NavLink to="/enterprise/messages" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><MailOutlined /> 站内消息</NavLink>
      <NavLink to="/enterprise/knowledge-bases" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><BookOutlined /> 企业知识库</NavLink>
      {managementRoles.has(role) && (
        <NavLink to="/enterprise/members" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><TeamOutlined /> 成员管理</NavLink>
      )}
      {managementRoles.has(role) && <button className="sidebar-item"><SettingOutlined /> 企业设置</button>}
    </aside>
  )
}

export default EnterpriseSidebar
