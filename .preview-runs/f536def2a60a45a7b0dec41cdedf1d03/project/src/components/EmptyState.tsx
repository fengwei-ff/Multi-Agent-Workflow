import { Empty } from 'antd-mobile'

export default function EmptyState({ description = '暂无数据' }: { description?: string }) {
  return <Empty description={description} />
}