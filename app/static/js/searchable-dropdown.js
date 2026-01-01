// Searchable Dropdown with Keyboard Navigation
function searchableDropdown(items, config = {}) {
    return {
        items: items || [],
        filteredItems: [],
        searchText: '',
        selectedIndex: -1,
        isOpen: false,
        selectedItem: null,
        
        init() {
            this.filteredItems = this.items;
        },
        
        filter() {
            const search = this.searchText.toLowerCase();
            this.filteredItems = this.items.filter(item => 
                this.getItemText(item).toLowerCase().includes(search)
            );
            this.selectedIndex = this.filteredItems.length > 0 ? 0 : -1;
            this.isOpen = true;
        },
        
        getItemText(item) {
            return typeof item === 'string' ? item : (config.displayKey ? item[config.displayKey] : item.name);
        },
        
        handleKeydown(e) {
            if (!this.isOpen && (e.key === 'ArrowDown' || e.key === 'Enter')) {
                this.isOpen = true;
                this.filter();
                e.preventDefault();
                return;
            }
            
            if (!this.isOpen) return;
            
            switch(e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    this.selectedIndex = Math.min(this.selectedIndex + 1, this.filteredItems.length - 1);
                    this.scrollToSelected();
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    this.selectedIndex = Math.max(this.selectedIndex - 1, 0);
                    this.scrollToSelected();
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (this.selectedIndex >= 0 && this.selectedIndex < this.filteredItems.length) {
                        this.select(this.filteredItems[this.selectedIndex]);
                    }
                    break;
                case 'Escape':
                    e.preventDefault();
                    this.isOpen = false;
                    break;
            }
        },
        
        select(item) {
            this.selectedItem = item;
            this.searchText = this.getItemText(item);
            this.isOpen = false;
            if (config.onSelect) config.onSelect(item);
        },
        
        scrollToSelected() {
            this.$nextTick(() => {
                const dropdown = this.$refs.dropdown;
                const selected = dropdown?.querySelector('[data-selected="true"]');
                if (selected) {
                    selected.scrollIntoView({ block: 'nearest' });
                }
            });
        }
    };
}
