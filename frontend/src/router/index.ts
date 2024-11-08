import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import OntologyGraph from '@/views/OntologyGraph.vue'
import OntologyCircles from '@/views/OntologyCircles.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/graph',
      name: 'graph',
      component: OntologyGraph
    },
    {
      path: '/circles',
      name: 'circles',
      component: OntologyCircles
    },
    {
      path: '/about',
      name: 'about',
      // route level code-splitting
      // this generates a separate chunk (About.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: () => import('../views/AboutView.vue')
    }
  ]
})

export default router
