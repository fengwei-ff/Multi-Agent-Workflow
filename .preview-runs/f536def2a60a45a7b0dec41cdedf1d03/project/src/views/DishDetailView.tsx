import { useEffect, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useParams } from 'react-router-dom'
import { Button, Card, Dialog, Rate, Skeleton, TextArea, Toast } from 'antd-mobile'
import AppNavBar from '../components/AppNavBar'
import LazyImage from '../components/LazyImage'
import { RootState } from '../store'
import { setCurrentDish, clearCurrentDish, toggleFavoriteLocal, setComments, appendComment, setNickname } from '../store/slices'
import { dishRepository, commentRepository, favoriteRepository, userRepository } from '../services'
import { FoodComment } from '../data/types'

const CATEGORY_NAMES: Record<string, string> = {
  main: '主料',
  side: '配菜',
  seasoning: '调料',
}

export default function DishDetailView() {
  const { dishId = '' } = useParams()
  const dispatch = useDispatch()
  const dish = useSelector((state: RootState) => state.dish.currentDish)
  const favoriteIds = useSelector((state: RootState) => state.favorite.favoriteIds)
  const comments = useSelector((state: RootState) => state.comment.commentsByDish[dishId] || [])
  const nickname = useSelector((state: RootState) => state.user.nickname)
  const isFavorite = favoriteIds.includes(dishId)

  const [rating, setRating] = useState(5)
  const [content, setContent] = useState('')

  useEffect(() => {
    dishRepository.getDishById(dishId).then(data => {
      if (data) dispatch(setCurrentDish(data))
    })
    commentRepository.getComments(dishId).then(commentList => {
      dispatch(setComments({ dishId, comments: commentList }))
    })
    return () => {
      dispatch(clearCurrentDish())
    }
  }, [dishId, dispatch])

  const handleToggleFavorite = async () => {
    if (isFavorite) {
      await favoriteRepository.removeFavorite(dishId)
    } else {
      await favoriteRepository.addFavorite(dishId)
    }
    dispatch(toggleFavoriteLocal(dishId))
    Toast.show(isFavorite ? '已取消收藏' : '收藏成功')
  }

  const handleSubmitComment = async () => {
    if (!content.trim()) return
    let currentNick = nickname
    if (!currentNick) {
      const result = window.prompt('请输入昵称', '')
      if (!result || !result.trim()) {
        Toast.show('昵称不能为空')
        return
      }
      currentNick = result.trim()
      userRepository.setNickname(currentNick)
      dispatch(setNickname(currentNick))
    }
    const comment: FoodComment = {
      id: `local_${Date.now()}`,
      dishId,
      nickname: currentNick,
      rating,
      content: content.trim(),
      createdAt: new Date().toISOString(),
    }
    await commentRepository.addComment(comment)
    dispatch(appendComment(comment))
    setContent('')
    setRating(5)
    Toast.show('评论成功')
  }

  if (!dish?.id || !dish?.ingredients) {
    return (
      <div className='page'>
        <AppNavBar title='菜品详情' />
        <Skeleton.Title animated />
      </div>
    )
  }

  const categories = ['main', 'side', 'seasoning'] as const

  return (
    <div className='page'>
      <AppNavBar title='菜品详情' />
      <LazyImage src={dish.thumbnail} alt={dish.name} className='detail-hero' />
      <div className='detail-header'>
        <h2>{dish.name}</h2>
        <div className='detail-desc'>{dish.description}</div>
        <Button
          size='small'
          color={isFavorite ? 'danger' : 'primary'}
          fill='outline'
          onClick={handleToggleFavorite}
        >
          {isFavorite ? '已收藏' : '收藏'}
        </Button>
      </div>

      <Card title='配料清单'>
        {categories.map(cat => (
          <div key={cat}>
            <h4>{CATEGORY_NAMES[cat]}</h4>
            {(dish.ingredients ?? []).filter(i => i.category === cat).map((ing, idx) => (
              <div key={idx} className='ingredient-row'>
                <span>{ing.name}</span>
                <span>{ing.amount}</span>
              </div>
            ))}
          </div>
        ))}
      </Card>

      <Card title='做法步骤'>
        {(dish.steps ?? []).map(step => (
          <div key={step.step} className='step-item'>
            <div className='step-num'>{step.step}</div>
            <div className='step-text'>{step.text}</div>
            {step.image && <LazyImage src={step.image} alt={`步骤${step.step}`} />}
          </div>
        ))}
      </Card>

      <Card title='评论'>
        <div className='comment-form'>
          <Rate allowClear value={rating} onChange={(val) => setRating(val || 5)} />
          <TextArea placeholder='说说你的感受吧~' value={content} onChange={setContent} rows={3} />
          <Button block color='primary' size='small' onClick={handleSubmitComment} disabled={!content.trim()}>
            提交评论
          </Button>
        </div>
        <div className='comment-list'>
          {comments.length === 0 ? <div className='empty-tip'>暂无评论，快来抢沙发！</div> : comments.map(comment => (
            <div key={comment.id} className='comment-item'>
              <div className='comment-header'>
                <span className='comment-nick'>{comment.nickname}</span>
                <Rate value={comment.rating} readOnly />
              </div>
              <div className='comment-content'>{comment.content}</div>
              <div className='comment-time'>{new Date(comment.createdAt).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}