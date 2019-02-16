const path = require('path')
const VueLoaderPlugin = require('vue-loader/lib/plugin')

function resolve (dir) {
  return path.join(__dirname, dir)
}

module.exports = {
    resolve: {
        extensions: ['.js', '.vue', '.json'],
        alias: {
            '@': resolve('src/'),
        }
    },
    module: {
        rules: [
            {
                test: /\.less$/,
                    use: [
                        'vue-style-loader',
                        'css-loader',
                        'less-loader'
                    ]
            },
            {
                test: /\.vue$/,
                loader: 'vue-loader'
            },
        ]
    },
    plugins: [
        new VueLoaderPlugin()
    ]
}
