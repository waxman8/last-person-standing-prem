/**
 * Shared utility functions for Last Person Standing frontend
 */

window.LMS_UTILS = {
    /**
     * Translates internal stage names and numbers to friendly labels.
     */
    STAGE_MAP: {
        1: 'Group Stage 1',
        2: 'Group Stage 2',
        3: 'Group Stage 3',
        4: 'Round of 32',
        5: 'Round of 16',
        6: 'Quarter Finals',
        7: 'Semi Finals',
        8: 'Final'
    },

    /**
     * Translates API stage names and gameweek numbers into friendly display names.
     * @param {Object} gw - The gameweek object (must have .number)
     * @param {Array} fixtures - (Optional) List of fixtures for this gameweek
     * @returns {string} Friendly stage name
     */
    getFriendlyStageName(gw, fixtures) {
        if (!gw) return 'Loading...';
        
        // Try to use the pre-defined number-based map first for consistency
        if (this.STAGE_MAP[gw.number]) {
            return this.STAGE_MAP[gw.number];
        }

        // Fallback to fixture-based detection if number isn't in map
        if (fixtures && fixtures.length > 0) {
            const stage = fixtures[0].stage;
            const mapping = {
                'GROUP_STAGE': `Group Stage ${gw.number}`,
                'ROUND_OF_32': 'Round of 32',
                'ROUND_OF_16': 'Round of 16',
                'QUARTER_FINALS': 'Quarter Finals',
                'SEMI_FINALS': 'Semi Finals',
                'FINAL': 'Final'
            };
            
            if (mapping[stage]) {
                return mapping[stage];
            }
        }
        
        return `Stage ${gw.number}`;
    }
};
