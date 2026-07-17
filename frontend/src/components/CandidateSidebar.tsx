import { BookOutlined, FileTextOutlined, LaptopOutlined, MessageOutlined, ReadOutlined, RobotOutlined, ScheduleOutlined } from '@ant-design/icons'
import { NavLink } from 'react-router-dom'

function CandidateSidebar() {
  return (
    <aside className="dashboard-sidebar">
      <div className="sidebar-title">个人工作台</div>
      <NavLink to="/candidate/dashboard" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><ReadOutlined /> 概览</NavLink>
      <NavLink to="/candidate/jobs" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><ScheduleOutlined /> 岗位与申请</NavLink>
      <NavLink to="/candidate/messages" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><MessageOutlined /> 站内消息</NavLink>
      <NavLink to="/candidate/enterprise-interviews" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><LaptopOutlined /> 企业面试</NavLink>
      <NavLink to="/candidate/interviews" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><RobotOutlined /> 模拟面试</NavLink>
      <NavLink to="/candidate/resumes" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><FileTextOutlined /> 我的简历</NavLink>
      <NavLink to="/candidate/knowledge-bases" className={({ isActive }) => `sidebar-item${isActive ? ' active' : ''}`}><BookOutlined /> 知识库</NavLink>
    </aside>
  )
}

export default CandidateSidebar
