module.exports = function(grunt) {
    grunt.loadNpmTasks('grunt-bowercopy');
    grunt.initConfig({
        bowercopy: {
            options: {clean: true},
            css: {
                options: {destPrefix: 'great/static/css/vendor'},
                files: {
                    'backgrid.css': 'backgrid/lib/backgrid.css',
                    'backgrid.filter.css': 'backgrid-filter/backgrid-filter.css',
                    'backgrid.paginator.css': 'backgrid-paginator/backgrid-paginator.css'
                }
            },
            js: {
                options: {destPrefix: 'great/static/js/vendor'},
                files: {
                    'backbone.paginator.js': 'backbone.paginator/lib/backbone.paginator.js',
                    'backgrid.js': 'backgrid/lib/backgrid.js',
                    'backgrid.filter.js': 'backgrid-filter/backgrid-filter.js',
                    'backgrid.paginator.js': 'backgrid-paginator/backgrid-paginator.js'
                }
            }
        }
    });
}
