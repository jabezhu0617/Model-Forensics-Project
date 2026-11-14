import { createApp } from 'vue';
import { createRouter, createWebHashHistory } from 'vue-router';
import App from './App.vue';
import Overview from './views/Overview.vue';
import HypothesisView from './views/HypothesisView.vue';
import ExperimentView from './views/ExperimentView.vue';
import RunView from './views/RunView.vue';
import Methods from './views/Methods.vue';
import TemporaryView from './views/TemporaryView.vue';
import './style.css';
const router=createRouter({history:createWebHashHistory(),routes:[
  {path:'/',component:Overview},
  {path:'/hypothesis/:id',component:HypothesisView},
  {path:'/experiment/:id',component:ExperimentView},
  {path:'/run/:id',component:RunView},
  {path:'/examples',component:TemporaryView},
  {path:'/examples/:id',component:RunView},
  {path:'/methods',component:Methods},
  {path:'/:pathMatch(.*)*',redirect:'/'},
],scrollBehavior:(to,from)=>to.path===from.path?false:{top:0}});
createApp(App).use(router).mount('#app');
