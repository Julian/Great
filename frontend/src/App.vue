<template>
  <div id="app">
    <nav class="uk-navbar-container" uk-navbar>
      <div class="uk-navbar-center">
        <ul class="uk-navbar-nav">
          <li><a href="#">Home</a></li>
          <li><a href="#">Radar</a></li>
          <li><a href="#">Tracked</a></li>
        </ul>
      </div>
    </nav>

    <div class="uk-container" id="app">
      <table class="uk-table">
        <caption>Radar</caption>
        <thead>
          <tr>
            <th>Artist</th>
            <th>Album</th>
          </tr>
        </thead>

        <tbody v-for="album in albums">
          <tr>
            <td>{{ album.artist.name }}</td>
            <td>{{ album.name }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import UIkit from 'uikit';
import Icons from 'uikit/dist/js/uikit-icons';
UIkit.use(Icons);

export default {
  data () {
    return {
      albums: [
        {name: "Something", artist: {name: "Someone"}},
        {name: "Another Thing", artist: {name: "Same One"}},
        {name: "A Third Thing", artist: {name: "A Different One"}},
      ],
    }
  }
}
</script>
