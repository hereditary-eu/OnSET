import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'
import OntologyGraph from '@/views/OntologyGraph.vue'
import OntologyCircles from '@/views/3D-Circles.vue'
import LinkedCircles from '@/views/LinkedOntology.vue'
import OntologyExplorative from '@/views/OntologyExplorative.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/explorative',
      name: 'explorative',
      component: OntologyExplorative
    },
    {
      path: '/graph',
      name: 'graph',
      component: OntologyGraph
    },
    {
      path: '/3d-circles',
      name: '3d-circles',
      component: OntologyCircles
    },
    {
      path: '/linked-circles',
      name: 'linked-circles',
      component: LinkedCircles
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
