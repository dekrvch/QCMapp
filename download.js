const filename = title.text+"_"+type+".csv" 
const filetext = csvString.text
console.log(csvString.text)
const blob = new Blob([filetext], { type: 'text/csv;charset=utf-8;' })
//alert('{ddddd}');

//addresses IE
if (navigator.msSaveBlob) {
    navigator.msSaveBlob(blob, filename)
} else {
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = filename
    link.target = '_blank'
    link.style.visibility = 'hidden'
    link.dispatchEvent(new MouseEvent('click'))
}