export interface Cuisine {
  id: string
  name: string
  description: string
  image: string
}

export interface Ingredient {
  name: string
  amount: string
  category: 'main' | 'side' | 'seasoning'
}

export interface Step {
  step: number
  text: string
  image?: string
}

export interface Dish {
  id: string
  cuisineId: string
  name: string
  description: string
  thumbnail: string
  images?: string[]
  ingredients: Ingredient[]
  steps: Step[]
}

export interface FoodComment {
  id: string
  dishId: string
  nickname: string
  rating: number
  content: string
  createdAt: string
}