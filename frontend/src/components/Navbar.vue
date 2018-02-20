<template>
  <nav class="uk-navbar-container" uk-navbar>
    <div class="uk-navbar-center">
      <ul class="uk-navbar-nav">
        <li><router-link to="/">Home</router-link></li>
        <li><router-link to="/radar">Radar</router-link></li>
        <li><router-link to="/tracked">Tracked</router-link></li>
      </ul>
    </div>
  </nav>
</template>

<script>
export default {
  name: 'Navbar',
};
</script>
