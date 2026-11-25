import { DislikeFilled, DislikeOutlined, LikeFilled, LikeOutlined } from '@ant-design/icons'
import { App, Button, Form, Input, Modal, Select, Space, Tooltip } from 'antd'
import { useState } from 'react'

import { errorText } from '../api/client'
import type { FeedbackCategory, FeedbackInput, TurnFeedback } from '../api/types'

const CATEGORIES: { value: FeedbackCategory; label: string }[] = [
  { value: 'wrong_intent', label: '理解错了需求' },
  { value: 'wrong_metric', label: '指标口径不对' },
  { value: 'wrong_sql', label: 'SQL 有问题' },
  { value: 'wrong_result', label: '查询结果不对' },
  { value: 'unclear', label: '解释不清楚' },
  { value: 'other', label: '其他' },
]
const COMMENT_LIMIT = 1000

interface FeedbackFields {
  category: FeedbackCategory
  comment: string
}

interface FeedbackProps {
  feedback?: TurnFeedback | null
  onSave: (feedback: FeedbackInput | null) => Promise<void>
}

/** 点赞直接保存，倒赞通过表单收集类型和说明。 */
export default function AnswerFeedback({ feedback, onSave }: FeedbackProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<FeedbackFields>()
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const liked = feedback?.rating === 'like'
  const disliked = feedback?.rating === 'dislike'

  const showEditor = () => {
    form.setFieldsValue({
      category: disliked ? feedback.category ?? undefined : undefined,
      comment: disliked ? feedback.comment : '',
    })
    setOpen(true)
  }

  const save = async (value: FeedbackInput | null) => {
    if (saving) return
    setSaving(true)
    try {
      await onSave(value)
      setOpen(false)
      void message.success(value ? '已记录反馈' : '已撤回反馈')
    } catch (error) {
      void message.error(`${value ? '反馈未保存' : '反馈未撤回'}：${errorText(error)}`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="answer-feedback">
      <Space size={4} role="group" aria-label="回答评价">
        <Tooltip title={liked ? '撤回点赞' : '点赞'}>
          <Button type="text" className="answer-feedback-button" icon={liked ? <LikeFilled /> : <LikeOutlined />}
            aria-label="点赞" aria-pressed={liked} loading={saving && !open} disabled={saving}
            onClick={() => void save(liked ? null : { rating: 'like' })} />
        </Tooltip>
        <Tooltip title={disliked ? '编辑或撤回倒赞' : '倒赞'}>
          <Button type="text" className="answer-feedback-button" icon={disliked ? <DislikeFilled /> : <DislikeOutlined />}
            aria-label="倒赞" aria-pressed={disliked} aria-haspopup="dialog" disabled={saving} onClick={showEditor} />
        </Tooltip>
      </Space>
      <Modal title={disliked ? '编辑回答反馈' : '反馈这条回答'} open={open} okText="提交反馈" cancelText="取消"
        confirmLoading={saving} cancelButtonProps={{ disabled: saving }} destroyOnHidden
        onOk={() => form.submit()} onCancel={() => { if (!saving) setOpen(false) }}
        footer={(_, { OkBtn, CancelBtn }) => (
          <>
            {disliked && <Button type="text" disabled={saving} onClick={() => void save(null)}>撤回倒赞</Button>}
            <CancelBtn />
            <OkBtn />
          </>
        )}>
        <Form form={form} layout="vertical" disabled={saving}
          onFinish={({ category, comment }) => void save({ rating: 'dislike', category, comment: comment.trim() })}>
          <Form.Item name="category" label="反馈类型" rules={[{ required: true, message: '请选择反馈类型' }]}>
            <Select options={CATEGORIES} placeholder="请选择" />
          </Form.Item>
          <Form.Item name="comment" label="反馈说明" rules={[{ required: true, whitespace: true, message: '请填写反馈说明' }]}>
            <Input.TextArea rows={4} showCount maxLength={COMMENT_LIMIT} placeholder="请说明哪里有问题，或者你期望得到什么结果" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
